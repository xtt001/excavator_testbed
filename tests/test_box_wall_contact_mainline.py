from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
    SafetyInterlockConfig,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS,
)
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from tests.test_box_wall_contact_semantics import (
    _obs,
    _pair,
    _pre,
    _wall_obs,
)


def _mainline_interlock() -> BoxEmptyingSafetyInterlock:
    return BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(
            wall_first_touch_mode=(
                WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
            ),
        )
    )


def test_new_mode_is_explicit_and_does_not_change_frozen_default() -> None:
    assert SafetyInterlockConfig().wall_first_touch_mode == "interrupt"
    assert (
        _mainline_interlock().config.wall_first_touch_mode
        == WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
    )


def test_adapter_preserves_explicit_mainline_mode_without_enabling_default() -> None:
    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            box_emptying={
                "safety_enabled": True,
                "safety": {
                    "wall_first_touch_mode": (
                        WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
                    ),
                },
            }
        )
    )

    assert (
        state.field_updates["box_emptying_cfg"]["safety"][
            "wall_first_touch_mode"
        ]
        == WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
    )


@pytest.mark.parametrize(
    "diagnostic_flag",
    (
        "wall_contact_diagnostic_ab_enabled",
        "wall_contact_diagnostic_observe_only_enabled",
    ),
)
def test_adapter_rejects_diagnostic_markers_for_mainline_mode(
    diagnostic_flag: str,
) -> None:
    with pytest.raises(ValueError, match="cannot use diagnostic markers"):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                box_emptying={
                    "safety": {
                        "wall_first_touch_mode": (
                            WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
                        ),
                        diagnostic_flag: True,
                    },
                }
            )
        )


def test_finite_bucket_contact_keeps_policy_action_and_records_evidence() -> None:
    interlock = _mainline_interlock()
    obs = _wall_obs(step_id=10, force_n=10_000.0)

    assert _pre(interlock, obs) is None
    decision = interlock.filter_action(
        obs,
        np.asarray([0.1, -0.2, 0.3, -0.4], dtype=np.float32),
        active_cell_id=0,
        active_corridor_id=0,
        skill_name="dig",
    )

    assert decision.action.tolist() == [
        np.float32(0.1),
        np.float32(-0.2),
        np.float32(0.3),
        np.float32(-0.4),
    ]
    assert decision.wall_contact_allowed is True
    assert decision.wall_contact_diagnostic_allowed is False
    assert decision.wall_contact_component == "bucket"
    assert (
        decision.debug_fields()["box_safety_wall_contact_allowed"] is True
    )


def test_separate_finite_bucket_sessions_remain_allowed() -> None:
    interlock = _mainline_interlock()

    assert _pre(interlock, _wall_obs(step_id=10, sessions=1)) is None
    assert _pre(interlock, _obs(step_id=11, wall_sessions=1)) is None
    assert _pre(interlock, _wall_obs(step_id=12, sessions=2)) is None


def test_boom_or_stick_contact_still_fails_closed() -> None:
    for component in ("boom", "stick"):
        interlock = _mainline_interlock()
        decision = _pre(
            interlock,
            _wall_obs(
                step_id=10,
                pairs=[_pair(component=component)],
            ),
        )

        assert decision is not None
        assert decision.reason == "wall_contact_forbidden_component"
        assert decision.awaiting_neutral_ack is True


def test_high_force_bucket_contact_still_fails_closed() -> None:
    interlock = _mainline_interlock()

    decision = _pre(
        interlock,
        _wall_obs(step_id=10, force_n=100_000.0),
    )

    assert decision is not None
    assert decision.reason == "wall_contact_high_force"
    assert decision.awaiting_neutral_ack is True
