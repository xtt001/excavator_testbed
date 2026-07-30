from __future__ import annotations

import json

import pytest

from testbed.planner.box_emptying.bottom_contact_detail import (
    BOTTOM_GATE_DIAGNOSTIC_ALLOW,
    BOTTOM_GATE_TERMINAL,
    WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
    WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED,
    WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX,
    FactoryFloorContactDetailContractError,
    FactoryFloorContactService,
    parse_worktool_factory_floor_contact_detail,
)


def _warning(
    *,
    step_id: int = 10,
    session_id: int = 1,
    consecutive_steps: int = 1,
    component: str = "bucket",
    normal_force_n: float = 20_000.0,
    tangential_force_n: float = 5_000.0,
    total_force_n: float = 21_000.0,
) -> str:
    payload = {
        "schema": "worktool_factory_floor_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.02,
        "delta_time_s": 0.02,
        "session_id": session_id,
        "session_count": session_id,
        "consecutive_contact_steps": consecutive_steps,
        "session_duration_s": consecutive_steps * 0.02,
        "step_max_normal_force_n": normal_force_n,
        "step_max_tangential_force_n": tangential_force_n,
        "step_max_total_force_n": total_force_n,
        "parts": [component],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"Machine/{component}/shape",
                "floor_shape_path": "FactoryFloor/shape",
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": normal_force_n,
                "max_tangential_force_n": tangential_force_n,
                "max_total_force_n": total_force_n,
                "contact_points_world_m": [[0.0, 0.0, 0.0]],
                "representative_contact_point_component_local_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
            }
        ],
    }
    return WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        allow_nan=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_parse_factory_floor_sidecar_validates_exact_lineage() -> None:
    detail = parse_worktool_factory_floor_contact_detail(
        [_warning()],
        expected_step_id=10,
        expected_sim_time_ns=200_000_000,
    )

    assert detail.parts == ("bucket",)
    assert detail.session_id == 1
    assert detail.pairs[0].floor_shape_path == "FactoryFloor/shape"
    assert detail.step_max_total_force_n == pytest.approx(21_000.0)


def test_parse_factory_floor_sidecar_accepts_unity_canonical_part_order() -> None:
    payload = json.loads(
        _warning().removeprefix(
            WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX
        )
    )
    stick_pair = dict(payload["pairs"][0])
    stick_pair["component"] = "stick"
    stick_pair["machine_shape_path"] = "Machine/stick/shape"
    payload["parts"] = ["stick", "bucket"]
    payload["pairs"] = [stick_pair, payload["pairs"][0]]
    warning = WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )

    detail = parse_worktool_factory_floor_contact_detail(
        [warning],
        expected_step_id=10,
        expected_sim_time_ns=200_000_000,
    )

    assert detail.parts == ("stick", "bucket")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.__setitem__("extra", 1),
        lambda payload: payload.__setitem__("step_id", 11),
        lambda payload: payload.__setitem__("parts", ["stick"]),
        lambda payload: payload.__setitem__(
            "step_max_total_force_n",
            float("nan"),
        ),
        lambda payload: payload["pairs"][0].__setitem__(
            "contact_point_count",
            0,
        ),
    ],
)
def test_parse_factory_floor_sidecar_rejects_contract_drift(mutate) -> None:
    warning = _warning()
    payload = json.loads(
        warning.removeprefix(WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX)
    )
    mutate(payload)
    encoded = WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        allow_nan=True,
        separators=(",", ":"),
        sort_keys=True,
    )

    with pytest.raises(FactoryFloorContactDetailContractError):
        parse_worktool_factory_floor_contact_detail(
            [encoded],
            expected_step_id=10,
            expected_sim_time_ns=200_000_000,
        )


def test_outside_footprint_bucket_sidecar_is_allowed_with_zero_107d_mask() -> None:
    service = FactoryFloorContactService()

    result = service.evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=[_warning()],
        step_id=10,
        sim_time_ns=200_000_000,
    )

    assert result.kind == BOTTOM_GATE_DIAGNOSTIC_ALLOW
    assert result.detail is not None
    assert result.detail.parts == ("bucket",)


def test_positive_107d_mask_requires_same_step_sidecar() -> None:
    result = FactoryFloorContactService().evaluate(
        typed_mask=1.0,
        aggregate_force_n=20_000.0,
        aggregate_session_count=1.0,
        warnings=[],
        step_id=10,
        sim_time_ns=200_000_000,
    )

    assert result.kind == BOTTOM_GATE_TERMINAL
    assert result.reason == "factory_floor_contact_detail_invalid"


@pytest.mark.parametrize(
    ("warnings", "reason"),
    [
        (
            [WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED],
            "factory_floor_contact_lineage_incomplete",
        ),
        (
            ["worktool_contact_monitor_status_v1:status=ready"],
            "factory_floor_contact_detail_invalid",
        ),
        (
            [
                WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
                WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED,
            ],
            "factory_floor_contact_detail_invalid",
        ),
    ],
)
def test_contact_monitor_status_is_exact_and_unambiguous(
    warnings: list[str],
    reason: str,
) -> None:
    result = FactoryFloorContactService().evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=warnings,
        step_id=10,
        sim_time_ns=200_000_000,
    )

    assert result.kind == BOTTOM_GATE_TERMINAL
    assert result.reason == reason


@pytest.mark.parametrize(
    ("warning", "reason"),
    [
        (
            WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
            "factory_floor_contact_lineage_incomplete",
        ),
        (
            "worktool_factory_floor_contact_lineage_incomplete_v1:{}",
            "factory_floor_contact_lineage_incomplete",
        ),
        (
            _warning(component="boom"),
            "factory_floor_contact_forbidden_component",
        ),
        (
            _warning(tangential_force_n=100_000.0, total_force_n=100_000.0),
            "factory_floor_contact_high_force",
        ),
        (
            _warning(normal_force_n=10_000.0, total_force_n=10_000.0),
            "factory_floor_contact_high_force",
        ),
    ],
)
def test_factory_floor_unsafe_sidecar_or_aggregate_is_terminal(
    warning: str,
    reason: str,
) -> None:
    aggregate_force = (
        100_000.0
        if warning.startswith(WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX)
        and "10000.0" in warning
        else 0.0
    )
    result = FactoryFloorContactService().evaluate(
        typed_mask=1.0 if aggregate_force else 0.0,
        aggregate_force_n=aggregate_force,
        aggregate_session_count=1.0 if aggregate_force else 0.0,
        warnings=[warning],
        step_id=10,
        sim_time_ns=200_000_000,
    )

    assert result.kind == BOTTOM_GATE_TERMINAL
    assert result.reason == reason


def test_factory_floor_sidecar_session_lineage_is_stateful() -> None:
    service = FactoryFloorContactService()

    first = service.evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=[_warning(step_id=10)],
        step_id=10,
        sim_time_ns=200_000_000,
    )
    second = service.evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=[
            _warning(
                step_id=11,
                consecutive_steps=2,
            )
        ],
        step_id=11,
        sim_time_ns=220_000_000,
    )
    clear = service.evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=[],
        step_id=12,
        sim_time_ns=240_000_000,
    )
    next_session = service.evaluate(
        typed_mask=0.0,
        aggregate_force_n=0.0,
        aggregate_session_count=0.0,
        warnings=[
            _warning(
                step_id=13,
                session_id=2,
            )
        ],
        step_id=13,
        sim_time_ns=260_000_000,
    )

    assert all(
        result.kind == BOTTOM_GATE_DIAGNOSTIC_ALLOW
        for result in (first, second, next_session)
    )
    assert clear.kind != BOTTOM_GATE_TERMINAL
