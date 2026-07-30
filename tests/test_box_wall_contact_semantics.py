from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.safety_effects import (
    SafetyDecisionCoverageEffectService,
)
from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
    SafetyInterlockConfig,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WORKTOOL_WALL_CONTACT_DETAIL_PREFIX,
    WallContactDetailContractError,
    parse_worktool_wall_contact_detail,
)
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


def _pair(
    *,
    component: str = "bucket",
    wall_name: str = "Dig_XMin_Board",
    total_force_n: float = 10_000.0,
) -> dict[str, object]:
    return {
        "component": component,
        "machine_shape_path": f"Machine/{component}/shape",
        "wall_name": wall_name,
        "wall_shape_path": f"DigArea/{wall_name}/shape",
        "callback_count": 1,
        "contact_point_count": 1,
        "max_normal_force_n": total_force_n,
        "max_tangential_force_n": 0.0,
        "max_total_force_n": total_force_n,
        "contact_points_world_m": [[1.0, 2.0, 3.0]],
        "representative_contact_point_component_local_m": [0.1, 0.2, 0.3],
        "tangential_displacement_m": 0.0,
    }


def _warning(
    *,
    step_id: int,
    session_count: int = 1,
    consecutive_contact_steps: int = 1,
    session_normal_impulse_n_s: float = 500.0,
    pairs: list[dict[str, object]] | None = None,
) -> str:
    contact_pairs = list(pairs or [_pair()])
    payload = {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.05,
        "delta_time_s": 0.05,
        "session_id": session_count,
        "session_count": session_count,
        "consecutive_contact_steps": consecutive_contact_steps,
        "session_duration_s": consecutive_contact_steps * 0.05,
        "session_normal_impulse_n_s": session_normal_impulse_n_s,
        "parts": sorted({str(pair["component"]) for pair in contact_pairs}),
        "walls": sorted({str(pair["wall_name"]) for pair in contact_pairs}),
        "pairs": contact_pairs,
    }
    return WORKTOOL_WALL_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        allow_nan=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _obs(
    *,
    step_id: int,
    wall: bool = False,
    wall_force_n: float = 0.0,
    wall_sessions: int = 0,
    bottom: bool = False,
    bottom_sessions: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[89] = 0.60
    env[90] = 1600.0
    env[91:97] = 0.2
    env[97:99] = 1920.0
    env[99:101] = 1.0
    env[101] = float(wall)
    env[102] = wall_force_n
    env[103] = wall_sessions
    env[104] = float(bottom)
    env[106] = bottom_sessions
    return {
        "step_id": step_id,
        "sim_time_ns": step_id * 50_000_000,
        "env_state": env,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "warnings": list(warnings or []),
    }


def _wall_obs(
    *,
    step_id: int,
    force_n: float = 10_000.0,
    sessions: int = 1,
    consecutive_steps: int = 1,
    pairs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    pair_values = list(pairs or [_pair(total_force_n=force_n)])
    return _obs(
        step_id=step_id,
        wall=True,
        wall_force_n=force_n,
        wall_sessions=sessions,
        warnings=[
            _warning(
                step_id=step_id,
                session_count=sessions,
                consecutive_contact_steps=consecutive_steps,
                pairs=pair_values,
            )
        ],
    )


def _pre(
    interlock: BoxEmptyingSafetyInterlock,
    obs: dict[str, object],
):
    return interlock.pre_policy_decision(
        obs,
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )


def test_parser_accepts_exact_canonical_bucket_pair() -> None:
    detail = parse_worktool_wall_contact_detail(
        [_warning(step_id=7)],
        expected_step_id=7,
        expected_sim_time_ns=350_000_000,
    )

    assert detail is not None
    assert detail.parts == ("bucket",)
    assert detail.walls == ("Dig_XMin_Board",)
    assert detail.pairs[0].component == "bucket"
    assert detail.pairs[0].contact_points_world_m == ((1.0, 2.0, 3.0),)


@pytest.mark.parametrize(
    "warnings,match",
    [
        ([], "missing"),
        (
            [_warning(step_id=7), _warning(step_id=7)],
            "ambiguous",
        ),
        (
            [
                _warning(
                        step_id=7,
                        pairs=[
                            _pair(component="boom"),
                            _pair(component="bucket"),
                        ],
                ).replace('"parts":["boom","bucket"]', '"parts":["bucket"]')
            ],
            "parts",
        ),
    ],
)
def test_parser_rejects_missing_ambiguous_or_inconsistent_lineage(
    warnings: list[str],
    match: str,
) -> None:
    with pytest.raises(WallContactDetailContractError, match=match):
        parse_worktool_wall_contact_detail(
            warnings,
            expected_step_id=7,
            expected_sim_time_ns=350_000_000,
        )


@pytest.mark.parametrize(
    "pairs,match",
    [
        ([_pair(component="unknown")], "component"),
        ([_pair(wall_name="Dig_Unknown_Board")], "wall"),
        (
            [
                _pair(component="bucket"),
                _pair(component="boom"),
            ],
            "deterministic",
        ),
    ],
)
def test_parser_rejects_unknown_or_non_deterministic_pairs(
    pairs: list[dict[str, object]],
    match: str,
) -> None:
    with pytest.raises(WallContactDetailContractError, match=match):
        parse_worktool_wall_contact_detail(
            [_warning(step_id=7, pairs=pairs)],
            expected_step_id=7,
            expected_sim_time_ns=350_000_000,
        )


def test_default_a_interrupts_first_bucket_contact_before_policy() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())

    decision = _pre(interlock, _wall_obs(step_id=10))

    assert decision is not None
    assert decision.reason == "wall_contact_first_session"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True
    assert decision.terminal is False
    acknowledged = _pre(
        interlock,
        _obs(step_id=11, wall_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is False
    assert acknowledged.replan is True
    assert acknowledged.next_skill == "return"


def test_diagnostic_a_interrupt_becomes_terminal_only_after_neutral_ack() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="interrupt",
        )
    )

    first = _pre(interlock, _wall_obs(step_id=10))
    assert first is not None
    assert first.reason == "wall_contact_first_session"
    assert first.awaiting_neutral_ack is True
    assert first.terminal is False

    acknowledged = _pre(
        interlock,
        _obs(step_id=11, wall_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert acknowledged.replan is False
    assert interlock.debug_fields()[
        "box_safety_wall_contact_diagnostic_ab_enabled"
    ] is True


def test_diagnostic_flag_does_not_stop_b_first_session() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
        )
    )

    assert _pre(interlock, _wall_obs(step_id=10)) is None


def test_positive_wall_without_sidecar_fails_closed_before_policy() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())

    decision = _pre(
        interlock,
        _obs(
            step_id=10,
            wall=True,
            wall_force_n=1.0,
            wall_sessions=1,
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_detail_invalid"
    assert decision.awaiting_neutral_ack is True
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    ("field_index", "non_finite_value"),
    [
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
            float("nan"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
            float("inf"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
            float("-inf"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
            float("nan"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
            float("inf"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
            float("-inf"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
            float("nan"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
            float("inf"),
        ),
        (
            ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
            float("-inf"),
        ),
    ],
)
def test_non_finite_wall_env_state_fails_closed_before_policy(
    field_index: int,
    non_finite_value: float,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    obs = _obs(step_id=10)
    env_state = np.asarray(obs["env_state"])
    env_state[field_index] = non_finite_value

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == "wall_contact_detail_invalid"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True
    assert decision.terminal is False

    acknowledged = _pre(interlock, _obs(step_id=11))
    assert acknowledged is not None
    assert acknowledged.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert acknowledged.replan is False


def test_finite_zero_wall_env_state_remains_valid_no_contact() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())

    decision = _pre(interlock, _obs(step_id=10))

    assert decision is None


def test_aggregate_normal_force_lineage_does_not_compare_against_total() -> None:
    pair = _pair(total_force_n=12_000.0)
    pair["max_normal_force_n"] = 10_000.0
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )

    decision = _pre(
        interlock,
        _wall_obs(step_id=10, force_n=10_000.0, pairs=[pair]),
    )

    assert decision is None


def test_aggregate_normal_force_lineage_mismatch_fails_closed() -> None:
    pair = _pair(total_force_n=10_000.0)
    pair["max_normal_force_n"] = 9_000.0
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )

    decision = _pre(
        interlock,
        _wall_obs(step_id=10, force_n=10_000.0, pairs=[pair]),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_detail_invalid"


@pytest.mark.parametrize("force_n", [100_000.0, 150_000.0, float("nan")])
def test_high_or_non_finite_force_is_terminal_before_policy(
    force_n: float,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )

    decision = _pre(interlock, _wall_obs(step_id=20, force_n=force_n))

    assert decision is not None
    assert decision.reason == "wall_contact_high_force"
    assert decision.awaiting_neutral_ack is True
    terminal = _pre(interlock, _obs(step_id=21))
    assert terminal is not None
    assert terminal.neutral_acknowledged is True
    assert terminal.terminal is True


def test_nan_force_with_nan_accumulated_impulse_uses_high_force_gate() -> None:
    warning = _warning(
        step_id=20,
        session_normal_impulse_n_s=float("nan"),
        pairs=[_pair(total_force_n=float("nan"))],
    )
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
        )
    )

    decision = _pre(
        interlock,
        _obs(
            step_id=20,
            wall=True,
            wall_force_n=float("nan"),
            wall_sessions=1,
            warnings=[warning],
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_high_force"


def test_unity_json_null_force_and_impulse_use_high_force_gate() -> None:
    encoded = _warning(step_id=20)
    payload = json.loads(encoded[len(WORKTOOL_WALL_CONTACT_DETAIL_PREFIX) :])
    payload["session_normal_impulse_n_s"] = None
    for field in (
        "max_normal_force_n",
        "max_tangential_force_n",
        "max_total_force_n",
    ):
        payload["pairs"][0][field] = None
    warning = WORKTOOL_WALL_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
        )
    )

    decision = _pre(
        interlock,
        _obs(
            step_id=20,
            wall=True,
            wall_force_n=float("nan"),
            wall_sessions=1,
            warnings=[warning],
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_high_force"


def test_json_null_outside_force_fields_remains_invalid_lineage() -> None:
    encoded = _warning(step_id=20)
    payload = json.loads(encoded[len(WORKTOOL_WALL_CONTACT_DETAIL_PREFIX) :])
    payload["pairs"][0]["tangential_displacement_m"] = None
    warning = WORKTOOL_WALL_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
        )
    )

    decision = _pre(
        interlock,
        _obs(
            step_id=20,
            wall=True,
            wall_force_n=10_000.0,
            wall_sessions=1,
            warnings=[warning],
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_detail_invalid"


def test_forbidden_component_precedes_nan_force_and_impulse() -> None:
    warning = _warning(
        step_id=20,
        session_normal_impulse_n_s=float("nan"),
        pairs=[
            _pair(
                component="stick",
                total_force_n=float("nan"),
            )
        ],
    )
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())

    decision = _pre(
        interlock,
        _obs(
            step_id=20,
            wall=True,
            wall_force_n=float("nan"),
            wall_sessions=1,
            warnings=[warning],
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_forbidden_component"


def test_same_session_force_escalation_preempts_act_and_becomes_terminal() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )

    assert _pre(interlock, _wall_obs(step_id=10, force_n=10_000.0)) is None
    decision = _pre(
        interlock,
        _wall_obs(
            step_id=11,
            force_n=150_000.0,
            consecutive_steps=2,
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_high_force"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_same_session_force_escalation_upgrades_pending_a_interrupt() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    first = _pre(interlock, _wall_obs(step_id=10, force_n=10_000.0))
    assert first is not None
    assert first.reason == "wall_contact_first_session"

    escalation = _pre(
        interlock,
        _wall_obs(
            step_id=11,
            force_n=150_000.0,
            consecutive_steps=2,
        ),
    )

    assert escalation is not None
    assert escalation.reason == "wall_contact_high_force"
    assert escalation.awaiting_neutral_ack is True
    assert escalation.neutral_acknowledged is False


def test_same_session_wall_drift_upgrades_pending_a_interrupt() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    assert _pre(interlock, _wall_obs(step_id=10)) is not None

    drift = _pre(
        interlock,
        _wall_obs(
            step_id=11,
            consecutive_steps=2,
            pairs=[_pair(wall_name="Dig_XMax_Board")],
        ),
    )

    assert drift is not None
    assert drift.reason == "wall_contact_identity_drift"
    assert drift.awaiting_neutral_ack is True


def test_bottom_contact_has_priority_over_simultaneous_wall_contact() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )
    obs = _obs(
        step_id=10,
        wall=True,
        wall_force_n=10_000.0,
        wall_sessions=1,
        bottom=True,
        bottom_sessions=1,
        warnings=[],
    )

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == "hard_bottom_contact"
    assert decision.contact_kind == "hard_bottom"


def test_wall_terminal_preempts_hard_bottom_pending_before_recovery_start() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    bottom = _pre(
        interlock,
        _obs(step_id=10, bottom=True, bottom_sessions=1),
    )
    assert bottom is not None
    assert bottom.reason == "hard_bottom_contact"

    wall = _pre(
        interlock,
        _wall_obs(step_id=11, force_n=100_000.0),
    )

    assert wall is not None
    assert wall.reason == "wall_contact_high_force"
    assert wall.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert wall.awaiting_neutral_ack is True
    assert wall.hard_bottom_recovery_active is False
    assert wall.event_id > bottom.event_id

    acknowledged = _pre(
        interlock,
        _obs(step_id=12, wall_sessions=1, bottom_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.reason == "wall_contact_high_force"
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert acknowledged.event_id == wall.event_id


@pytest.mark.parametrize(
    ("terminal_kind", "expected_reason"),
    [
        ("high_force", "wall_contact_high_force"),
        ("missing_lineage", "wall_contact_detail_invalid"),
    ],
)
def test_wall_terminal_preempts_scripted_hard_bottom_recovery(
    terminal_kind: str,
    expected_reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    assert (
        _pre(
            interlock,
            _obs(step_id=20, bottom=True, bottom_sessions=1),
        )
        is not None
    )
    bottom_ack = _pre(
        interlock,
        _obs(step_id=21, bottom_sessions=1),
    )
    assert bottom_ack is not None
    assert bottom_ack.hard_bottom_recovery_active is True

    wall_obs = (
        _wall_obs(step_id=22, force_n=100_000.0)
        if terminal_kind == "high_force"
        else _obs(
            step_id=22,
            wall=True,
            wall_force_n=10_000.0,
            wall_sessions=1,
            warnings=[],
        )
    )
    wall = _pre(interlock, wall_obs)

    assert wall is not None
    assert wall.reason == expected_reason
    assert wall.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert wall.awaiting_neutral_ack is True
    assert wall.hard_bottom_clearance_active is False
    assert wall.hard_bottom_recovery_active is False

    acknowledged = _pre(
        interlock,
        _obs(step_id=23, wall_sessions=1, bottom_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.reason == expected_reason
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True


def test_b_allows_entire_first_continuous_bucket_wall_session() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )
    action = np.full(4, 0.25, dtype=np.float32)

    for step_id in (10, 11, 12):
        obs = _wall_obs(
            step_id=step_id,
            force_n=10_000.0 + step_id,
            consecutive_steps=step_id - 9,
        )
        assert _pre(interlock, obs) is None
        filtered = interlock.filter_action(
            obs,
            action,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        )
        assert filtered.action.tolist() == pytest.approx(action.tolist())
        assert filtered.wall_contact_diagnostic_allowed is True


def test_b_contact_free_tick_consumes_exception_and_later_contact_terminates() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    decision = _pre(
        interlock,
        _wall_obs(step_id=12, sessions=2),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_repeat_session"
    assert decision.awaiting_neutral_ack is True


def test_b_contact_free_tick_consumes_exception_even_if_counter_does_not_advance() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    decision = _pre(interlock, _wall_obs(step_id=12, sessions=1))

    assert decision is not None
    assert decision.reason == "wall_contact_repeat_session"


def test_b2_single_clear_tick_keeps_same_logical_session() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    resumed = _wall_obs(step_id=12, sessions=2)
    assert _pre(interlock, resumed) is None
    filtered = interlock.filter_action(
        resumed,
        np.full(4, 0.25, dtype=np.float32),
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert filtered.wall_contact_diagnostic_allowed is True
    assert interlock.debug_fields()[
        "box_safety_wall_contact_session_end_clear_ticks"
    ] == 2


def test_b2_raw_session_rollover_must_start_at_first_contact_step() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    decision = _pre(
        interlock,
        _wall_obs(
            step_id=12,
            sessions=2,
            consecutive_steps=2,
        ),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_identity_drift"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_b2_multiple_single_clear_gaps_remain_one_logical_session() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None
    assert _pre(interlock, _wall_obs(step_id=12, sessions=2)) is None
    assert _pre(interlock, _obs(step_id=13, wall_sessions=2)) is None

    resumed = _wall_obs(step_id=14, sessions=3)

    assert _pre(interlock, resumed) is None
    assert (
        interlock.filter_action(
            resumed,
            np.full(4, 0.25, dtype=np.float32),
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        ).wall_contact_diagnostic_allowed
        is True
    )


def test_b2_reset_clears_logical_session_gap_state() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    interlock.reset()
    fresh = _wall_obs(step_id=0, sessions=1)

    assert _pre(interlock, fresh) is None
    assert (
        interlock.filter_action(
            fresh,
            np.full(4, 0.25, dtype=np.float32),
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        ).wall_contact_diagnostic_allowed
        is True
    )


def test_b2_two_consecutive_clear_ticks_end_session() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None
    assert _pre(interlock, _obs(step_id=12, wall_sessions=1)) is None

    decision = _pre(interlock, _wall_obs(step_id=13, sessions=2))

    assert decision is not None
    assert decision.reason == "wall_contact_repeat_session"
    assert decision.awaiting_neutral_ack is True


@pytest.mark.parametrize(
    ("force_n", "pairs", "expected_reason"),
    [
        (
            10_000.0,
            [_pair(component="boom")],
            "wall_contact_forbidden_component",
        ),
        (
            10_000.0,
            [_pair(wall_name="Dig_XMax_Board")],
            "wall_contact_identity_drift",
        ),
        (
            100_000.0,
            None,
            "wall_contact_high_force",
        ),
    ],
)
def test_b2_tolerated_clear_tick_does_not_relax_hard_stops(
    force_n: float,
    pairs: list[dict[str, object]] | None,
    expected_reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None

    decision = _pre(
        interlock,
        _wall_obs(
            step_id=12,
            sessions=2,
            force_n=force_n,
            pairs=pairs,
        ),
    )

    assert decision is not None
    assert decision.reason == expected_reason
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_b2_tolerated_clear_tick_does_not_preempt_hard_bottom() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None
    simultaneous = _wall_obs(step_id=12, sessions=2)
    env = np.asarray(simultaneous["env_state"])
    env[104] = 1.0
    env[106] = 1.0

    decision = _pre(interlock, simultaneous)

    assert decision is not None
    assert decision.reason == "hard_bottom_contact"
    assert decision.contact_kind == "hard_bottom"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_b2_allowed_contact_still_reaches_stuck_hard_stop() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=2,
            stuck_window_steps=2,
        )
    )
    proposed = np.full(4, 0.25, dtype=np.float32)
    first = _wall_obs(step_id=10, sessions=1, consecutive_steps=1)
    second = _wall_obs(step_id=11, sessions=1, consecutive_steps=2)

    assert _pre(interlock, first) is None
    assert (
        interlock.filter_action(
            first,
            proposed,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        ).wall_contact_diagnostic_allowed
        is True
    )
    assert _pre(interlock, second) is None
    stopped = interlock.filter_action(
        second,
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert stopped.reason == "stuck_50_steps"
    assert stopped.terminal is False
    assert stopped.awaiting_neutral_ack is True
    assert stopped.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    acknowledged = _pre(
        interlock,
        _obs(step_id=12, wall_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.reason == "stuck_50_steps"
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True


def test_observe_only_allows_bucket_sessions_and_wall_changes_without_effects() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )
    )
    proposed = np.asarray([0.20, -0.30, 0.40, -0.50], dtype=np.float32)
    contacts = (
        _wall_obs(
            step_id=10,
            sessions=1,
            consecutive_steps=1,
            pairs=[
                _pair(
                    wall_name="Dig_XMin_Board",
                    total_force_n=20_000.0,
                )
            ],
            force_n=20_000.0,
        ),
        _wall_obs(
            step_id=11,
            sessions=1,
            consecutive_steps=2,
            pairs=[
                _pair(
                    wall_name="Dig_ZMax_Board",
                    total_force_n=25_000.0,
                )
            ],
            force_n=25_000.0,
        ),
        _wall_obs(
            step_id=13,
            sessions=2,
            consecutive_steps=1,
            pairs=[
                _pair(
                    wall_name="Dig_XMax_Board",
                    total_force_n=30_000.0,
                )
            ],
            force_n=30_000.0,
        ),
    )

    decisions = []
    for index, obs in enumerate(contacts):
        if index == 2:
            assert _pre(
                interlock,
                _obs(step_id=12, wall_sessions=1),
            ) is None
        assert _pre(interlock, obs) is None
        decision = interlock.filter_action(
            obs,
            proposed,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        )
        decisions.append(decision)
        assert decision.action.tolist() == pytest.approx(proposed.tolist())
        assert decision.reason == ""
        assert decision.terminal is False
        assert decision.awaiting_neutral_ack is False
        assert decision.neutral_acknowledged is False
        assert decision.replan is False
        assert decision.next_skill == ""
        assert decision.blocked_corridor_id == -1
        assert decision.contact_kind == "none"
        assert decision.policy_restarted is False
        assert decision.wall_contact_diagnostic_allowed is True

    coverage_state = CoverageRuntimeState()
    effect = SafetyDecisionCoverageEffectService(coverage_state).apply(
        decisions[-1]
    )
    assert effect.applied is False
    assert coverage_state.coverage_depth_exhausted_physical_cell_ids == set()
    debug = interlock.debug_fields()
    assert debug["box_safety_wall_contact_diagnostic_ab_enabled"] is False
    assert (
        debug["box_safety_wall_contact_diagnostic_observe_only_enabled"]
        is True
    )
    assert debug["box_safety_wall_first_touch_mode"] == (
        "record_bucket_all_contacts"
    )


def test_observe_only_allows_multiple_bucket_walls_in_one_tick() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )
    )
    obs = _wall_obs(
        step_id=10,
        sessions=1,
        consecutive_steps=1,
        force_n=30_000.0,
        pairs=[
            _pair(
                wall_name="Dig_XMax_Board",
                total_force_n=30_000.0,
            ),
            _pair(
                wall_name="Dig_ZMin_Board",
                total_force_n=20_000.0,
            ),
        ],
    )

    assert _pre(interlock, obs) is None
    decision = interlock.filter_action(
        obs,
        np.full(4, 0.25, dtype=np.float32),
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert decision.wall_contact_diagnostic_allowed is True
    assert decision.wall_contact_component == "bucket"
    assert decision.wall_contact_wall_name == (
        "Dig_XMax_Board,Dig_ZMin_Board"
    )


@pytest.mark.parametrize(
    ("obs", "reason"),
    [
        (
            _wall_obs(
                step_id=10,
                pairs=[_pair(component="boom")],
            ),
            "wall_contact_forbidden_component",
        ),
        (
            _wall_obs(step_id=10, force_n=100_000.0),
            "wall_contact_high_force",
        ),
        (
            _obs(
                step_id=10,
                wall=True,
                wall_force_n=10_000.0,
                wall_sessions=1,
            ),
            "wall_contact_detail_invalid",
        ),
    ],
)
def test_observe_only_does_not_relax_wall_hard_stops(
    obs: dict[str, object],
    reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )
    )

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == reason
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True


def test_observe_only_rejects_sidecar_when_wall_mask_is_clear() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )
    )
    obs = _obs(
        step_id=10,
        wall=False,
        wall_force_n=0.0,
        wall_sessions=0,
        warnings=[_warning(step_id=10)],
    )

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == "wall_contact_detail_invalid"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_observe_only_does_not_preempt_hard_bottom_terminal() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )
    )
    obs = _wall_obs(step_id=10)
    env = np.asarray(obs["env_state"])
    env[104] = 1.0
    env[106] = 1.0

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == "hard_bottom_contact"
    assert decision.contact_kind == "hard_bottom"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    acknowledged = _pre(
        interlock,
        _obs(step_id=11, bottom_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert acknowledged.replan is False


def test_observe_only_allowed_contact_still_reaches_stuck_stop() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
            stuck_window_steps=2,
        )
    )
    proposed = np.full(4, 0.25, dtype=np.float32)
    first = _wall_obs(step_id=10, sessions=1, consecutive_steps=1)
    second = _wall_obs(step_id=11, sessions=1, consecutive_steps=2)

    assert _pre(interlock, first) is None
    assert (
        interlock.filter_action(
            first,
            proposed,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        ).wall_contact_diagnostic_allowed
        is True
    )
    assert _pre(interlock, second) is None
    stopped = interlock.filter_action(
        second,
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert stopped.reason == "stuck_50_steps"
    assert stopped.action.tolist() == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    "pairs,reason",
    [
        ([_pair(component="boom")], "wall_contact_forbidden_component"),
        (
            [_pair(component="bucket", wall_name="Dig_XMax_Board")],
            "wall_contact_identity_drift",
        ),
    ],
)
def test_b_component_or_wall_drift_is_terminal(
    pairs: list[dict[str, object]],
    reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session"
        )
    )
    assert _pre(interlock, _wall_obs(step_id=10)) is None

    decision = _pre(
        interlock,
        _wall_obs(
            step_id=11,
            consecutive_steps=2,
            pairs=pairs,
        ),
    )

    assert decision is not None
    assert decision.reason == reason
    assert decision.awaiting_neutral_ack is True


def test_wall_first_touch_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="wall_first_touch_mode"):
        SafetyInterlockConfig(wall_first_touch_mode="silently_ignore")


def test_bucket_first_session_mode_requires_explicit_diagnostic_marker() -> None:
    with pytest.raises(
        ValueError,
        match="record_bucket_first_session requires "
        "wall_contact_diagnostic_ab_enabled",
    ):
        SafetyInterlockConfig(
            wall_first_touch_mode="record_bucket_first_session"
        )


def test_observe_only_mode_requires_its_explicit_diagnostic_marker() -> None:
    with pytest.raises(
        ValueError,
        match="record_bucket_all_contacts requires "
        "wall_contact_diagnostic_observe_only_enabled",
    ):
        SafetyInterlockConfig(
            wall_first_touch_mode="record_bucket_all_contacts"
        )


def test_observe_only_marker_is_mode_scoped_and_mutually_exclusive() -> None:
    with pytest.raises(
        ValueError,
        match="observe-only diagnostic marker requires",
    ):
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
        )


def test_wall_high_force_threshold_cannot_relax_fixed_100kn_gate() -> None:
    with pytest.raises(ValueError, match="100000"):
        SafetyInterlockConfig(wall_high_force_n=100_001.0)


@pytest.mark.parametrize("value", [0, 3, True, 1.5, 2.0])
def test_session_end_clear_ticks_rejects_out_of_scope_values(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="session_end_clear_ticks"):
        SafetyInterlockConfig(
            wall_contact_diagnostic_ab_enabled=True,
            wall_first_touch_mode="record_bucket_first_session",
            wall_contact_session_end_clear_ticks=value,  # type: ignore[arg-type]
        )


def test_two_clear_tick_semantics_requires_diagnostic_b_mode() -> None:
    with pytest.raises(
        ValueError,
        match="two-clear-tick session semantics requires",
    ):
        SafetyInterlockConfig(
            wall_contact_session_end_clear_ticks=2,
        )


def test_adapter_rejects_unknown_wall_first_touch_mode_during_normalization() -> None:
    with pytest.raises(ValueError, match="wall_first_touch_mode"):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_first_touch_mode": "silently_ignore",
                    },
                }
            )
        )


def test_adapter_rejects_unmarked_bucket_first_session_mode() -> None:
    with pytest.raises(
        ValueError,
        match="record_bucket_first_session requires "
        "wall_contact_diagnostic_ab_enabled",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_first_touch_mode": (
                            "record_bucket_first_session"
                        ),
                    },
                }
            )
        )


def test_adapter_rejects_unmarked_observe_only_mode() -> None:
    with pytest.raises(
        ValueError,
        match="record_bucket_all_contacts requires "
        "wall_contact_diagnostic_observe_only_enabled",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_first_touch_mode": (
                            "record_bucket_all_contacts"
                        ),
                    },
                }
            )
        )


def test_adapter_requires_boolean_diagnostic_ab_marker() -> None:
    with pytest.raises(
        ValueError,
        match="wall_contact_diagnostic_ab_enabled",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_contact_diagnostic_ab_enabled": "true",
                    },
                }
            )
        )


def test_adapter_requires_boolean_observe_only_marker() -> None:
    with pytest.raises(
        ValueError,
        match="wall_contact_diagnostic_observe_only_enabled",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_contact_diagnostic_observe_only_enabled": "true",
                    },
                }
            )
        )


def test_adapter_rejects_unmarked_two_clear_tick_session_semantics() -> None:
    with pytest.raises(
        ValueError,
        match="two-clear-tick session semantics requires",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety_enabled": True,
                    "safety": {
                        "wall_contact_session_end_clear_ticks": 2,
                    },
                }
            )
        )
